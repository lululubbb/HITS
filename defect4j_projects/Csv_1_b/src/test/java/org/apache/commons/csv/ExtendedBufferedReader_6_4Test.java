package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_6_4Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            // Override read() to delegate to mockReader.read()
            @Override
            public int read() throws IOException {
                return mockReader.read();
            }

            @Override
            public void mark(int readAheadLimit) throws IOException {
                mockReader.mark(readAheadLimit);
            }

            @Override
            public void reset() throws IOException {
                mockReader.reset();
            }
        };
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsNextChar() throws IOException {
        when(mockReader.read()).thenReturn((int) 'A');
        doNothing().when(mockReader).mark(1);
        doNothing().when(mockReader).reset();

        int result = extendedBufferedReader.lookAhead();

        assertEquals('A', result);
        verify(mockReader).mark(1);
        verify(mockReader).read();
        verify(mockReader).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStream() throws IOException {
        when(mockReader.read()).thenReturn(ExtendedBufferedReader.END_OF_STREAM);
        doNothing().when(mockReader).mark(1);
        doNothing().when(mockReader).reset();

        int result = extendedBufferedReader.lookAhead();

        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
        verify(mockReader).mark(1);
        verify(mockReader).read();
        verify(mockReader).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOException() throws IOException {
        doThrow(new IOException("mark failed")).when(mockReader).mark(1);

        IOException thrown = assertThrows(IOException.class, () -> extendedBufferedReader.lookAhead());
        assertEquals("mark failed", thrown.getMessage());
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOExceptionOnRead() throws IOException {
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenThrow(new IOException("read failed"));

        IOException thrown = assertThrows(IOException.class, () -> extendedBufferedReader.lookAhead());
        assertEquals("read failed", thrown.getMessage());
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOExceptionOnReset() throws IOException {
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenReturn((int) 'B');
        doThrow(new IOException("reset failed")).when(mockReader).reset();

        IOException thrown = assertThrows(IOException.class, () -> extendedBufferedReader.lookAhead());
        assertEquals("reset failed", thrown.getMessage());
    }

    @Test
    @Timeout(8000)
    void testLookAheadViaReflection() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        when(mockReader.read()).thenReturn((int) 'Z');
        doNothing().when(mockReader).mark(1);
        doNothing().when(mockReader).reset();

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);
        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);

        assertEquals('Z', result);
        verify(mockReader).mark(1);
        verify(mockReader).read();
        verify(mockReader).reset();
    }
}