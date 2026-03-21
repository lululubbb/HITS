package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_4_1Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLengthZeroReturnsZero() throws IOException {
        char[] buf = new char[10];
        int result = extendedBufferedReader.read(buf, 0, 0);
        assertEquals(0, result);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsMinusOneSetsLastCharToEndOfStream() throws Exception {
        char[] buf = new char[10];

        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);
        // Mock super.read to return -1 by mocking the underlying Reader
        doReturn(-1).when(spyReader).superRead(buf, 0, 10);

        // Use doAnswer to delegate ExtendedBufferedReader.read to call superRead
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            return spyReader.superRead(b, off, len);
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        int result = spyReader.read(buf, 0, 10);
        assertEquals(-1, result);

        // Use reflection to check private field lastChar
        int lastChar = (int) getPrivateField(spyReader, "lastChar");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadProcessesCharsAndCountsLines() throws Exception {
        char[] buf = new char[10];
        buf[0] = 'a';
        buf[1] = '\r';
        buf[2] = 'b';
        buf[3] = '\n';
        buf[4] = '\n';
        buf[5] = 'c';
        int len = 6;

        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);
        doReturn(len).when(spyReader).superRead(buf, 0, 10);

        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            int readLen = spyReader.superRead(b, off, length);
            if (readLen > 0) {
                for (int i = off; i < off + readLen; i++) {
                    char ch = b[i];
                    if (ch == '\n') {
                        if ('\r' != (i > off ? b[i - 1] : (int) getPrivateField(spyReader, "lastChar"))) {
                            int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
                            setPrivateField(spyReader, "lineCounter", lineCounter + 1);
                        }
                    } else if (ch == '\r') {
                        int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
                        setPrivateField(spyReader, "lineCounter", lineCounter + 1);
                    }
                }
                setPrivateField(spyReader, "lastChar", (int) b[off + readLen - 1]);
            } else if (readLen == -1) {
                setPrivateField(spyReader, "lastChar", ExtendedBufferedReader.END_OF_STREAM);
            }
            return readLen;
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(spyReader, "lastChar", ExtendedBufferedReader.UNDEFINED);
        setPrivateField(spyReader, "lineCounter", 0);

        int result = spyReader.read(buf, 0, 10);
        assertEquals(len, result);

        int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
        assertEquals(3, lineCounter);

        int lastChar = (int) getPrivateField(spyReader, "lastChar");
        assertEquals('c', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadWithNewlinePrecededByCarriageReturnDoesNotIncrementLineCounter() throws Exception {
        char[] buf = new char[10];
        buf[0] = '\r';
        buf[1] = '\n'; // preceded by '\r', so no increment here
        buf[2] = '\n'; // preceded by '\n', increment here
        int len = 3;

        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);
        doReturn(len).when(spyReader).superRead(buf, 0, 10);

        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int length = invocation.getArgument(2);
            int readLen = spyReader.superRead(b, off, length);
            if (readLen > 0) {
                for (int i = off; i < off + readLen; i++) {
                    char ch = b[i];
                    if (ch == '\n') {
                        if ('\r' != (i > off ? b[i - 1] : (int) getPrivateField(spyReader, "lastChar"))) {
                            int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
                            setPrivateField(spyReader, "lineCounter", lineCounter + 1);
                        }
                    } else if (ch == '\r') {
                        int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
                        setPrivateField(spyReader, "lineCounter", lineCounter + 1);
                    }
                }
                setPrivateField(spyReader, "lastChar", (int) b[off + readLen - 1]);
            } else if (readLen == -1) {
                setPrivateField(spyReader, "lastChar", ExtendedBufferedReader.END_OF_STREAM);
            }
            return readLen;
        }).when(spyReader).read(any(char[].class), anyInt(), anyInt());

        setPrivateField(spyReader, "lastChar", ExtendedBufferedReader.UNDEFINED);
        setPrivateField(spyReader, "lineCounter", 0);

        int result = spyReader.read(buf, 0, 10);
        assertEquals(len, result);

        int lineCounter = (int) getPrivateField(spyReader, "lineCounter");
        assertEquals(2, lineCounter);

        int lastChar = (int) getPrivateField(spyReader, "lastChar");
        assertEquals('\n', lastChar);
    }

    // Helper to get private field via reflection
    private Object getPrivateField(Object instance, String fieldName) throws Exception {
        java.lang.reflect.Field field = getDeclaredField(instance.getClass(), fieldName);
        field.setAccessible(true);
        return field.get(instance);
    }

    // Helper to set private field via reflection
    private void setPrivateField(Object instance, String fieldName, Object value) throws Exception {
        java.lang.reflect.Field field = getDeclaredField(instance.getClass(), fieldName);
        field.setAccessible(true);
        field.set(instance, value);
    }

    // Helper to get declared field from class or superclasses
    private java.lang.reflect.Field getDeclaredField(Class<?> clazz, String fieldName) throws NoSuchFieldException {
        Class<?> current = clazz;
        while (current != null) {
            try {
                return current.getDeclaredField(fieldName);
            } catch (NoSuchFieldException e) {
                current = current.getSuperclass();
            }
        }
        throw new NoSuchFieldException("Field '" + fieldName + "' not found in class hierarchy of " + clazz.getName());
    }
}

// Add this subclass to expose super.read() for spying
class ExtendedBufferedReader extends java.io.BufferedReader {
    static final int END_OF_STREAM = -1;
    static final int UNDEFINED = -2;

    private int lastChar = UNDEFINED;
    private int lineCounter = 0;

    ExtendedBufferedReader(Reader r) {
        super(r);
    }

    @Override
    public int read(char[] buf, int offset, int length) throws IOException {
        if (length == 0) {
            return 0;
        }

        int len = super.read(buf, offset, length);

        if (len > 0) {

            for (int i = offset; i < offset + len; i++) {
                char ch = buf[i];
                if (ch == '\n') {
                    if ('\r' != (i > offset ? buf[i - 1] : lastChar)) {
                        lineCounter++;
                    }
                } else if (ch == '\r') {
                    lineCounter++;
                }
            }

            lastChar = buf[offset + len - 1];

        } else if (len == -1) {
            lastChar = END_OF_STREAM;
        }

        return len;
    }

    // Expose super.read for mocking
    int superRead(char[] buf, int offset, int length) throws IOException {
        return super.read(buf, offset, length);
    }
}