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

class ExtendedBufferedReader_4_3Test {

    ExtendedBufferedReader readerSpy;

    @BeforeEach
    void setUp() throws Exception {
        Reader mockReader = mock(Reader.class);
        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);
        readerSpy = Mockito.spy(reader);
        // To avoid infinite recursion when spying read(char[], int, int),
        // stub the super.read call via doCallRealMethod and partial mocking
        doCallRealMethod().when(readerSpy).read(any(char[].class), anyInt(), anyInt());
    }

    @Test
    @Timeout(8000)
    void testRead_lengthZero_returnsZero() throws IOException {
        char[] buf = new char[10];
        int result = readerSpy.read(buf, 0, 0);
        assertEquals(0, result);
        // The read method itself calls super.read internally, so we verify super.read is never called.
        // But since read is spied with doCallRealMethod, the internal super.read is called.
        // So this verify is invalid and should be removed or changed.
        // Instead, verify that the underlying reader's read is never called.
        Reader in = getPrivateField(readerSpy, "in");
        verify(in, never()).read(any(char[].class), anyInt(), anyInt());
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_noNewlineOrReturn() throws IOException {
        char[] buf = new char[10];
        // Prepare a char array with no '\n' or '\r'
        buf[0] = 'a';
        buf[1] = 'b';
        buf[2] = 'c';

        Reader in = getPrivateField(readerSpy, "in");
        doAnswer(invocation -> {
            char[] argumentBuf = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, argumentBuf, offset, 3);
            return 3;
        }).when(in).read(any(char[].class), anyInt(), anyInt());

        // Reset lineCounter and lastChar to initial states
        setPrivateField(readerSpy, "lineCounter", 0);
        setPrivateField(readerSpy, "lastChar", ExtendedBufferedReader.UNDEFINED);

        int result = readerSpy.read(new char[10], 0, 3);
        assertEquals(3, result);

        int lineCounter = getPrivateField(readerSpy, "lineCounter");
        int lastChar = getPrivateField(readerSpy, "lastChar");

        assertEquals(0, lineCounter);
        assertEquals('c', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlineNotPrecededByCarriageReturn() throws IOException {
        char[] buf = new char[10];
        // buf contains: a \n b
        buf[0] = 'a';
        buf[1] = '\n';
        buf[2] = 'b';

        Reader in = getPrivateField(readerSpy, "in");
        doAnswer(invocation -> {
            char[] argumentBuf = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, argumentBuf, offset, 3);
            return 3;
        }).when(in).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lineCounter", 0);
        setPrivateField(readerSpy, "lastChar", ExtendedBufferedReader.UNDEFINED);

        int result = readerSpy.read(new char[10], 0, 3);
        assertEquals(3, result);

        int lineCounter = getPrivateField(readerSpy, "lineCounter");
        int lastChar = getPrivateField(readerSpy, "lastChar");

        assertEquals(1, lineCounter);
        assertEquals('b', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withNewlinePrecededByCarriageReturn() throws IOException {
        char[] buf = new char[10];
        // buf contains: \r \n b
        buf[0] = '\r';
        buf[1] = '\n';
        buf[2] = 'b';

        Reader in = getPrivateField(readerSpy, "in");
        doAnswer(invocation -> {
            char[] argumentBuf = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, argumentBuf, offset, 3);
            return 3;
        }).when(in).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lineCounter", 0);
        setPrivateField(readerSpy, "lastChar", ExtendedBufferedReader.UNDEFINED);

        int result = readerSpy.read(new char[10], 0, 3);
        assertEquals(3, result);

        int lineCounter = getPrivateField(readerSpy, "lineCounter");
        int lastChar = getPrivateField(readerSpy, "lastChar");

        assertEquals(1, lineCounter);
        assertEquals('b', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenPositive_withCarriageReturn() throws IOException {
        char[] buf = new char[10];
        // buf contains: a \r b \r
        buf[0] = 'a';
        buf[1] = '\r';
        buf[2] = 'b';
        buf[3] = '\r';

        Reader in = getPrivateField(readerSpy, "in");
        doAnswer(invocation -> {
            char[] argumentBuf = invocation.getArgument(0);
            int offset = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            System.arraycopy(buf, 0, argumentBuf, offset, 4);
            return 4;
        }).when(in).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lineCounter", 0);
        setPrivateField(readerSpy, "lastChar", ExtendedBufferedReader.UNDEFINED);

        int result = readerSpy.read(new char[10], 0, 4);
        assertEquals(4, result);

        int lineCounter = getPrivateField(readerSpy, "lineCounter");
        int lastChar = getPrivateField(readerSpy, "lastChar");

        assertEquals(2, lineCounter);
        assertEquals('\r', lastChar);
    }

    @Test
    @Timeout(8000)
    void testRead_lenMinusOne_setsLastCharToEndOfStream() throws IOException {
        char[] buf = new char[10];

        Reader in = getPrivateField(readerSpy, "in");
        doReturn(-1).when(in).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(readerSpy, "lastChar", 'x');

        int result = readerSpy.read(buf, 0, 5);
        assertEquals(-1, result);

        int lastChar = getPrivateField(readerSpy, "lastChar");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
    }

    // Helper methods to access private fields using reflection
    @SuppressWarnings("unchecked")
    private <T> T getPrivateField(Object instance, String fieldName) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return (T) field.get(instance);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private void setPrivateField(Object instance, String fieldName, Object value) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            field.set(instance, value);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}