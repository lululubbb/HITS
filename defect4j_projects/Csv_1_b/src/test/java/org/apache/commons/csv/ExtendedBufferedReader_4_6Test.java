package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_4_6Test {

    private ExtendedBufferedReader reader;
    private Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        reader = new ExtendedBufferedReader(mockReader) {
            // Override read(char[], int, int) to call super.read(char[], int, int) on BufferedReader
            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return super.read(cbuf, off, len);
            }
        };
    }

    @Test
    @Timeout(8000)
    void testRead_lengthZero_returnsZero() throws IOException {
        char[] buf = new char[10];
        int result = reader.read(buf, 0, 0);
        assertEquals(0, result);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_noNewlineOrReturn() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(reader);
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            // Fill buf with 'a' (no \n or \r)
            for (int i = off; i < off + len; i++) {
                b[i] = 'a';
            }
            return len;
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        // Initialize lineCounter and lastChar to known values before calling read
        setPrivateIntField(spyReader, "lineCounter", 0);
        setPrivateIntField(spyReader, "lastChar", ExtendedBufferedReader.UNDEFINED);

        char[] bufTest = new char[10];
        int readLen = spyReader.read(bufTest, 2, 5);
        assertEquals(5, readLen);

        // Verify buffer filled correctly
        for (int i = 2; i < 7; i++) {
            assertEquals('a', bufTest[i]);
        }

        // lineCounter should remain 0
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals(0, lineCounter);

        // lastChar should be last char read 'a'
        int lastChar = getPrivateIntField(spyReader, "lastChar");
        assertEquals('a', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlineNotPrecededByReturn() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(reader);
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            // Fill with: a, \n, b, \n, \r starting at offset 1, length 5
            b[off] = 'a';
            b[off + 1] = '\n';
            b[off + 2] = 'b';
            b[off + 3] = '\n';
            b[off + 4] = '\r';
            return len;
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        // Set lastChar to something other than '\r' (e.g. 'x')
        setPrivateIntField(spyReader, "lastChar", 'x');
        setPrivateIntField(spyReader, "lineCounter", 0);

        char[] bufTest = new char[10];
        int readLen = spyReader.read(bufTest, 1, 5);
        assertEquals(5, readLen);

        // lineCounter increments:
        // '\n' at buf[off+1] preceded by 'a' (not '\r') => +1
        // '\n' at buf[off+3] preceded by 'b' (not '\r') => +1
        // '\r' at buf[off+4] => +1
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals(3, lineCounter);

        // lastChar should be '\r' (buf[offset + len -1])
        int lastChar = getPrivateIntField(spyReader, "lastChar");
        assertEquals('\r', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlinePrecededByReturn() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(reader);
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            // Fill with: \r, \n, \r, \n starting at offset 0, length 4
            b[off] = '\r';
            b[off + 1] = '\n';
            b[off + 2] = '\r';
            b[off + 3] = '\n';
            return len;
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateIntField(spyReader, "lastChar", ExtendedBufferedReader.UNDEFINED);
        setPrivateIntField(spyReader, "lineCounter", 0);

        char[] bufTest = new char[10];
        int readLen = spyReader.read(bufTest, 0, 4);
        assertEquals(4, readLen);

        // lineCounter increments:
        // '\r' at buf[0] => +1
        // '\n' at buf[1] preceded by '\r' => no increment
        // '\r' at buf[2] => +1
        // '\n' at buf[3] preceded by '\r' => no increment
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals(2, lineCounter);

        // lastChar should be '\n'
        int lastChar = getPrivateIntField(spyReader, "lastChar");
        assertEquals('\n', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenMinusOne_setsLastCharToEndOfStream() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(reader);
        doAnswer(invocation -> -1).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateIntField(spyReader, "lastChar", 'x');
        char[] buf = new char[10];
        int result = spyReader.read(buf, 0, 5);
        assertEquals(-1, result);

        int lastChar = getPrivateIntField(spyReader, "lastChar");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
    }

    private int getPrivateIntField(Object obj, String fieldName) throws Exception {
        Field field = getDeclaredFieldIncludingSuperclass(obj.getClass(), fieldName);
        field.setAccessible(true);
        return field.getInt(obj);
    }

    private void setPrivateIntField(Object obj, String fieldName, int value) throws Exception {
        Field field = getDeclaredFieldIncludingSuperclass(obj.getClass(), fieldName);
        field.setAccessible(true);
        field.setInt(obj, value);
    }

    private Field getDeclaredFieldIncludingSuperclass(Class<?> clazz, String fieldName) throws NoSuchFieldException {
        Class<?> current = clazz;
        while (current != null) {
            try {
                return current.getDeclaredField(fieldName);
            } catch (NoSuchFieldException e) {
                current = current.getSuperclass();
            }
        }
        throw new NoSuchFieldException(fieldName);
    }
}